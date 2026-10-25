from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from great_scratchpad.grounded_recall import (
    CALL_OUTPUT_TOKENS, ROLES, assess_answer, audit_stage, build_plan,
    canonical_json_sha256, experiment_config, load_plan, offline_checks,
    prepare_grounded_recall, reference_answer, render_records, run_grounded_recall,
    strict_json, validate_case, validate_suite,
)

REPO = Path(__file__).resolve().parents[1]
CASES = REPO / "scenarios" / "grounded_recall_v2_cases.json"
CONFIGS = [
    {"profile": "test-luna", "backend": "openai", "adapter": "openai-responses",
     "model": "test-luna", "api_key_env": "TEST_LUNA", "max_output_tokens": 900},
    {"profile": "test-mistral", "backend": "openai-compatible", "model": "test-mistral",
     "api_key_env": "TEST_MISTRAL", "max_tokens": 400},
]


class GroundedAssessorTests(unittest.TestCase):
    def setUp(self):
        self.suite = json.loads(CASES.read_text(encoding="utf-8"))
        self.case = self.suite["cases"][0]

    def assess(self, answer, visible=True):
        return assess_answer(json.dumps(answer, ensure_ascii=False), self.case, visible)

    def test_offline_contract_corpus(self):
        validate_suite(self.suite)
        result = offline_checks(self.suite)
        self.assertGreater(result["total"], 180)
        self.assertEqual(result["total"], result["passed"])

    def test_declared_paraphrase_without_old_marker_words(self):
        answer = reference_answer(self.case)
        answer["rejected_alternative"]["value"] = "基板間の差異"
        answer["accepted_unit"]["value"] = "一枚の基板の端子間差異"
        answer["comparison_boundary"]["value"] = "接続の配置形状に限定"
        self.assertTrue(self.assess(answer)["passed"])

    def test_negation_and_reversal_fail_with_valid_quotes(self):
        answer = reference_answer(self.case)
        answer["accepted_unit"]["value"] = "同じ基板内の端子差ではない"
        self.assertFalse(self.assess(answer)["passed"])
        answer = reference_answer(self.case)
        answer["accepted_unit"]["value"], answer["rejected_alternative"]["value"] = (
            answer["rejected_alternative"]["value"], answer["accepted_unit"]["value"],
        )
        result = self.assess(answer)
        self.assertFalse(result["passed"])
        self.assertTrue(result["roles"]["accepted_unit"]["citation_ok"])
        self.assertFalse(result["roles"]["accepted_unit"]["value_ok"])

    def test_absence_is_neither_adoption_nor_refutation(self):
        for status in ("established", "refuted"):
            answer = reference_answer(self.case)
            answer["prior_adoption"]["status"] = status
            result = self.assess(answer)
            self.assertFalse(result["passed"])
            self.assertEqual(result["recovered_roles"], 3)

    def test_explicit_nonadoption_requires_earlier_evidence(self):
        self.case["records"][0]["text"] = "比較案「基板どうしの差」は初回から採用していない。"
        self.case["truth"]["prior_adoption"] = {
            "status": "refuted", "evidence": [{"source_id": "r1", "quote": self.case["records"][0]["text"]}],
        }
        validate_case(self.case)
        answer = reference_answer(self.case)
        self.assertTrue(self.assess(answer)["passed"])
        answer["prior_adoption"]["evidence"] = answer["rejected_alternative"]["evidence"]
        self.assertFalse(self.assess(answer)["passed"])

    def test_earlier_adoption_and_current_rejection_are_separate(self):
        self.case = self.suite["cases"][1]
        answer = reference_answer(self.case)
        self.assertTrue(self.assess(answer)["passed"])
        answer["prior_adoption"]["evidence"] = answer["rejected_alternative"]["evidence"]
        self.assertFalse(self.assess(answer)["passed"])

    def test_hidden_evidence_cannot_be_cited_and_abstention_is_not_recovery(self):
        self.assertFalse(self.assess(reference_answer(self.case), visible=False)["passed"])
        result = self.assess(reference_answer(self.case, False), visible=False)
        self.assertTrue(result["passed"])
        self.assertTrue(result["abstention_ok"])
        self.assertEqual(result["recovered_roles"], 0)

    def test_all_citations_must_support_the_claim(self):
        answer = reference_answer(self.case)
        answer["accepted_unit"]["evidence"].append({"source_id": "r1", "quote": self.case["records"][0]["text"]})
        self.assertFalse(self.assess(answer)["passed"])
        answer = reference_answer(self.case)
        answer["accepted_unit"]["evidence"][0]["quote"] = "同じ基板内の端子差"
        self.assertFalse(self.assess(answer)["passed"])

    def test_undeclared_paraphrase_fails_closed_without_hallucination_claim(self):
        answer = reference_answer(self.case)
        answer["accepted_unit"]["value"] = "単一の基板の各端子に見られる差"
        result = self.assess(answer)
        self.assertIn("accepted_unit:undeclared_value", result["errors"])

    def test_strict_schema_handles_untrusted_shapes(self):
        for value in (None, [], 7, "text", {}):
            self.assertFalse(self.assess(value)["schema_ok"])
        for role in (*ROLES, "prior_adoption"):
            for bad in ([], 9, False, {"value": [1]}, {"status": [], "evidence": []}):
                answer = reference_answer(self.case)
                answer[role] = bad
                self.assertFalse(self.assess(answer)["schema_ok"])
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '```json\n{}\n```'):
            self.assertFalse(assess_answer(raw, self.case, True)["schema_ok"])

    def test_extra_prose_cannot_hide_contradictory_claims(self):
        answer = reference_answer(self.case)
        answer["message"] = "以前は基板間比較を採用していた。"
        self.assertFalse(self.assess(answer)["schema_ok"])

    def test_object_null_abstention_remains_schema_failure_in_frozen_v2(self):
        answer = {role: {"value": None, "evidence": []} for role in ROLES}
        answer["prior_adoption"] = {"status": "not_established", "evidence": []}
        result = self.assess(answer, visible=False)
        self.assertFalse(result["schema_ok"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["recovered_roles"], 0)

    def test_fixture_rejects_future_sources_and_nonhistorical_adoption(self):
        for mutation in ("future", "missing", "historical", "alias"):
            case = deepcopy(self.suite["cases"][1])
            if mutation == "future":
                case["records"][0]["turn"] = case["probe_turn"]
            elif mutation == "missing":
                case["truth"]["accepted_unit"]["evidence"][0]["source_id"] = "absent"
            elif mutation == "historical":
                case["records"][0]["turn"] = 2
            else:
                case["truth"]["accepted_unit"]["aliases"].append(case["truth"]["rejected_alternative"]["value"])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_case(case)


class GroundedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan_dir = self.root / "run"
        self.profiles = [cfg["profile"] for cfg in CONFIGS]
        (self.root / "llm.json").write_text(json.dumps({"profiles": {c["profile"]: c for c in CONFIGS}}))
        self.env = patch.dict("os.environ", {"TEST_LUNA": "secret-test-luna", "TEST_MISTRAL": "secret-test-mistral"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def prepare(self):
        self.envelope = prepare_grounded_recall(self.root, CASES, self.profiles, self.plan_dir)
        self.plan = self.envelope["plan"]
        self.digest = self.envelope["plan_sha256"]
        return self.envelope

    def run_stage(self, stage):
        return run_grounded_recall(self.root, self.plan_dir, self.digest, stage)

    def fake_response(self, cfg, prompt, system):
        cell = next(c for c in self.plan["cells"] if c["profile"] == cfg["profile"] and c["prompt"] == prompt)
        case = next(c for c in self.plan["suite"]["cases"] if c["id"] == cell["case_id"])
        return {"content": json.dumps(reference_answer(case, cell["condition"] != "none"), ensure_ascii=False),
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "estimated": False},
                "response_model": cfg["model"], "model": cfg["model"], "profile": cfg["profile"]}

    def test_prepare_no_calls_or_secrets_and_all_48_prompts_fixed(self):
        with patch("great_scratchpad.grounded_recall.call_llm_result") as call, patch(
            "great_scratchpad.grounded_recall.api_key_from_config", side_effect=AssertionError("No secret reads")
        ):
            self.prepare()
        call.assert_not_called()
        self.assertEqual(len(self.plan["cells"]), 48)
        self.assertEqual(sum(c["stage"] == "calibration" for c in self.plan["cells"]), 16)
        self.assertNotIn("secret-test", (self.plan_dir / "plan.json").read_text())
        self.assertEqual(load_plan(self.root, self.plan_dir, self.digest), self.plan)
        self.assertEqual(self.plan["budget"]["max_output_tokens"], 48000)
        self.assertEqual(self.plan["configs"][0]["max_output_tokens"], CALL_OUTPUT_TOKENS)
        self.assertEqual(self.plan["configs"][1]["max_tokens"], CALL_OUTPUT_TOKENS)

    def test_shared_history_original_records_and_no_alias_leak(self):
        self.prepare()
        self.assertEqual(len({c["outside_memory_sha256"] for c in self.plan["cells"]}), 1)
        for case in self.plan["suite"]["cases"]:
            original = render_records(case, "original")
            for condition in ("prose", "roles"):
                self.assertTrue(render_records(case, condition).startswith(original + "\n\n"))
            for cell in (c for c in self.plan["cells"] if c["case_id"] == case["id"]):
                for role in ROLES:
                    for alias in case["truth"][role]["aliases"]:
                        self.assertNotIn(alias, cell["prompt"])
                    if cell["condition"] == "none":
                        self.assertNotIn(case["truth"][role]["value"], cell["prompt"])
                        self.assertEqual(cell["visible_source_ids"], [])

    def test_budget_exceeded_never_makes_call_or_directory(self):
        with patch("great_scratchpad.grounded_recall.call_llm_result") as call:
            for kwargs in ({"max_api_calls": 47}, {"max_output_tokens": 47999}):
                with self.assertRaises(ValueError):
                    prepare_grounded_recall(self.root, CASES, self.profiles, self.plan_dir, **kwargs)
        call.assert_not_called()
        self.assertFalse(self.plan_dir.exists())

    def test_no_overwrite_even_prepare(self):
        self.prepare()
        before = (self.plan_dir / "plan.json").read_bytes()
        with self.assertRaises(FileExistsError):
            prepare_grounded_recall(self.root, CASES, self.profiles, self.plan_dir)
        self.assertEqual((self.plan_dir / "plan.json").read_bytes(), before)

    def test_full_fake_calibration_then_confirmation(self):
        self.prepare()
        with patch("great_scratchpad.grounded_recall.call_llm_result", side_effect=self.fake_response) as call:
            calibration = self.run_stage("calibration")
            self.assertEqual(call.call_count, 16)
            self.assertTrue(calibration["gate_passed"])
            confirmation = self.run_stage("confirmation")
            self.assertEqual(call.call_count, 48)
            self.assertTrue(confirmation["gate_passed"])
            self.assertEqual(confirmation["usage"]["completion_tokens"], 640)
            with self.assertRaises(FileExistsError):
                self.run_stage("calibration")
            with self.assertRaises(FileExistsError):
                self.run_stage("confirmation")
            self.assertEqual(call.call_count, 48)
        audit = audit_stage(self.plan, self.digest, self.plan_dir / "confirmation", "confirmation")
        self.assertTrue(audit["passed"])

    def test_failed_calibration_blocks_confirmation_with_raw_retained(self):
        self.prepare()
        with patch("great_scratchpad.grounded_recall.call_llm_result", return_value={"content": "invalid json"}) as call:
            calibration = self.run_stage("calibration")
            self.assertEqual(calibration["status"], "complete")
            self.assertFalse(calibration["gate_passed"])
            with self.assertRaisesRegex(ValueError, "Calibration failed"):
                self.run_stage("confirmation")
            self.assertEqual(call.call_count, 16)
        self.assertFalse((self.plan_dir / "confirmation").exists())
        lines = (self.plan_dir / "calibration" / "responses.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 16)
        self.assertEqual(json.loads(lines[0])["raw_output"], "invalid json")

    def test_attempt_recorded_before_call_and_transport_failure_redacted(self):
        self.prepare()

        def fail(*args):
            result = json.loads((self.plan_dir / "calibration" / "result.json").read_text())
            self.assertEqual(result["attempted_calls"], 1)
            self.assertEqual(result["cells"][0]["status"], "running")
            raise RuntimeError("failed secret-test-luna and secret-test-mistral")

        with patch("great_scratchpad.grounded_recall.call_llm_result", side_effect=fail) as call:
            result = self.run_stage("calibration")
            self.assertEqual(result["status"], "error")
            self.assertEqual(call.call_count, 1)
            with self.assertRaises(FileExistsError):
                self.run_stage("calibration")
        self.assertNotIn("secret-test", json.dumps(result))

    def test_interrupt_does_not_resume_or_pass_gate(self):
        self.prepare()
        with patch("great_scratchpad.grounded_recall.call_llm_result", side_effect=KeyboardInterrupt):
            result = self.run_stage("calibration")
        self.assertEqual(result["attempted_calls"], 1)
        self.assertEqual(result["status"], "error")
        with patch("great_scratchpad.grounded_recall.call_llm_result") as call:
            with self.assertRaises((ValueError, FileNotFoundError)):
                self.run_stage("confirmation")
        call.assert_not_called()

    def test_raw_receipt_saved_before_assessment(self):
        self.prepare()

        def inspect(raw, case, visible):
            self.assertTrue((self.plan_dir / "calibration" / "responses.jsonl").exists())
            raise RuntimeError("assessment interrupted")

        original = assess_answer
        with patch("great_scratchpad.grounded_recall.call_llm_result", side_effect=self.fake_response):
            # Preparation revalidates offline checks before the output directory exists.
            with patch("great_scratchpad.grounded_recall.assess_answer", side_effect=lambda *args: (
                inspect(*args) if (self.plan_dir / "calibration").exists() else original(*args)
            )):
                result = self.run_stage("calibration")
        self.assertEqual(result["status"], "error")
        self.assertEqual(len((self.plan_dir / "calibration" / "responses.jsonl").read_text().splitlines()), 1)

    def test_missing_keys_preflight_without_stage_dir(self):
        self.prepare()
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(SystemExit):
            self.run_stage("calibration")
        self.assertFalse((self.plan_dir / "calibration").exists())

    def test_tampered_plan_code_or_config_blocks_calls(self):
        self.prepare()
        with patch("great_scratchpad.grounded_recall.call_llm_result") as call:
            with self.assertRaises(ValueError):
                run_grounded_recall(self.root, self.plan_dir, "bad-digest", "calibration")
            with patch("great_scratchpad.grounded_recall.runtime_hashes", return_value={}), self.assertRaises(ValueError):
                self.run_stage("calibration")
            altered = {**CONFIGS[0], "temperature": 0.9}
            with patch("great_scratchpad.grounded_recall.load_llm_config", side_effect=[altered, CONFIGS[1]]):
                with self.assertRaises(ValueError):
                    self.run_stage("calibration")
            self.envelope["plan"]["cells"][0]["prompt"] += "changed"
            (self.plan_dir / "plan.json").write_text(json.dumps(self.envelope))
            with self.assertRaises(ValueError):
                self.run_stage("calibration")
        call.assert_not_called()

    def test_confirmation_rejects_tampered_gate_missing_or_changed_raw(self):
        self.prepare()
        with patch("great_scratchpad.grounded_recall.call_llm_result", side_effect=self.fake_response):
            self.run_stage("calibration")
        result_path = self.plan_dir / "calibration" / "result.json"
        raw_path = self.plan_dir / "calibration" / "responses.jsonl"
        original_result, original_raw = result_path.read_text(), raw_path.read_text()
        for change in ("gate", "partial", "reordered", "raw", "assessment"):
            result, rows = json.loads(original_result), original_raw.splitlines()
            if change == "gate":
                result["gate_passed"] = False
            elif change == "partial":
                rows.pop()
            elif change == "reordered":
                rows[0], rows[1] = rows[1], rows[0]
            elif change == "raw":
                row = json.loads(rows[0])
                row["raw_output"] = "{}"
                rows[0] = json.dumps(row)
            else:
                result["cells"][0]["assessment"]["passed"] = False
            result_path.write_text(json.dumps(result))
            raw_path.write_text("\n".join(rows) + "\n")
            with self.subTest(change=change), patch("great_scratchpad.grounded_recall.call_llm_result") as call:
                with self.assertRaises(ValueError):
                    self.run_stage("confirmation")
                call.assert_not_called()
        self.assertFalse((self.plan_dir / "confirmation").exists())

    def test_no_silent_credential_or_history_config_persistence(self):
        for key in ("api_key", "previous_response_id", "response_format", "command"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                experiment_config({**CONFIGS[0], key: "not-permitted"})

    def test_strict_json_duplicate_and_nonfinite(self):
        for raw in ('{"a":1,"a":2}', '{"a":Infinity}', '{"a":NaN}'):
            with self.assertRaises(ValueError):
                strict_json(raw)

    def test_legacy_scenarios_unchanged_by_prepare(self):
        paths = sorted((REPO / "scenarios").glob("luna_*.json"))
        before = {str(path): canonical_json_sha256(json.loads(path.read_text())) for path in paths}
        self.prepare()
        after = {str(path): canonical_json_sha256(json.loads(path.read_text())) for path in paths}
        self.assertEqual(before, after)

    def test_case_partition_must_not_reuse_calibration_cases(self):
        suite = json.loads(CASES.read_text())
        suite["cases"][2] = deepcopy(suite["cases"][0])
        with self.assertRaises(ValueError):
            build_plan(suite, CONFIGS)


if __name__ == "__main__":
    unittest.main()
