from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from great_scratchpad.dialogue import canonical_json_sha256
from great_scratchpad.experiments import write_manifest
from great_scratchpad.memory_task_design import SYSTEM, assess_task_answer, source_text
from great_scratchpad.reinjection import linked_condition
from great_scratchpad.storage import load_llm_config
from great_scratchpad.uncertainty_contract import (
    FLAG_STATES, SYSTEMS, assess_answer, make_state_case,
    parse_answer, reference_state, routing_value,
)
from great_scratchpad.uncertainty_experiment import (
    SPEC, SPEC_V21, assess_receipt, audit_stage, build_plan, load_plan, prepare, request_params, run, summarize,
)

REPO = Path(__file__).resolve().parents[1]
CONFIG = str(REPO / "examples/mistral-large-4.json")
SPEC_PATH = REPO / "scenarios/uncertainty_contract_v2.json"
CFG = load_llm_config(REPO, CONFIG, "mistral-large-4-high")


def answer_for(case, visible=None):
    state = reference_state(case, visible)
    return {"status": state["status"], "value": state["value"],
            "evidence": state["support"], "flags": state["flags"]}


def prompt_for(case, visible=None):
    return "\n".join(source_text(r) for r in case["records"] if visible is None or r["id"] in visible)


class UncertaintyContractTests(unittest.TestCase):
    def test_all_sixteen_flag_combinations_with_independent_expected_table(self):
        table = {
            "enabled": ["held_value"] * 4,
            "disabled": ["fast", "base", None, None],
            "unknown": [None] * 4, "unobserved": [None] * 4,
        }
        for hold in FLAG_STATES:
            for index, urgent in enumerate(FLAG_STATES):
                with self.subTest(urgent=urgent, hold=hold):
                    self.assertEqual(routing_value(urgent, hold), table[hold][index])
        with self.assertRaises(ValueError):
            routing_value("false", "disabled")

    def test_authored_scenarios_have_independent_status_and_flag_expectations(self):
        expected = {"hold-unknown": (None, "disabled", "unknown"),
                    "urgent-unknown": (None, "unknown", "disabled"),
                    "hold-dominates": ("HOLD", "unknown", "enabled"),
                    "urgent-enabled": ("FAST", "enabled", "disabled"),
                    "base-route": ("BASE", "disabled", "disabled"),
                    "hold-unobserved": (None, "disabled", "unobserved")}
        for scenario, (prefix, urgent, hold) in expected.items():
            case = make_state_case(101, scenario, "test")
            truth = reference_state(case)
            self.assertEqual(truth["flags"], {"urgent": urgent, "hold": hold})
            self.assertTrue(truth["value"].startswith(prefix) if prefix else truth["value"] is None)
            self.assertTrue(truth["support"])
        for scenario in ("proposals-only", "pending-join"):
            truth = reference_state(make_state_case(101, scenario, "test"))
            self.assertIsNone(truth["value"])
            self.assertEqual(len(truth["support"]), 3)

    def test_visible_reference_matches_all_flag_pairs_and_needs_rules(self):
        case = make_state_case(101, "base-route", "test")
        request = next(r for r in case["records"] if r["kind"] == "request")
        override = next(r for r in case["records"] if r["kind"] == "override")
        policy = next(r for r in case["records"] if r["kind"] == "policy")
        for hold in FLAG_STATES:
            for urgent in FLAG_STATES:
                request["flag_states"] = {"urgent": urgent, "hold": hold}
                expected = (override["held_value"] if hold == "enabled" else
                            policy["fast"] if hold == "disabled" and urgent == "enabled" else
                            policy["base"] if hold == "disabled" and urgent == "disabled" else None)
                self.assertEqual(reference_state(case)["value"], expected)
                self.assertIsNone(reference_state(case, [request["id"]])["value"])
                self.assertIsNone(reference_state(case, [request["id"], policy["id"]])["value"])

    def test_exported_schema_states_and_status_constraints_match_validator(self):
        schema = json.loads((REPO / "schemas/evidence_state_v2.schema.json").read_text())
        self.assertEqual(schema["required"], ["status", "value", "evidence", "flags"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["else"]["properties"]["value"]["type"], "null")
        flags = schema["properties"]["flags"]["oneOf"][1]["properties"]
        self.assertEqual(flags["hold"]["enum"], list(FLAG_STATES))
        self.assertEqual(flags["urgent"]["enum"], list(FLAG_STATES))

    def test_evidence_bearing_unknown_valid_new_but_frozen_legacy_stays_invalid(self):
        case = make_state_case(101, "hold-unknown", "test")
        answer = answer_for(case)
        raw = json.dumps(answer)
        score = assess_answer(raw, case, prompt_for(case), "evidence-state")
        self.assertTrue(score["contract_success"])
        self.assertFalse(score["recovered"])
        legacy = json.dumps({k: answer[k] for k in ("value", "evidence")})
        self.assertFalse(assess_task_answer(legacy, case, prompt_for(case))["schema_ok"])
        self.assertFalse(assess_answer(legacy, case, prompt_for(case), "legacy")["schema_ok"])
        self.assertTrue(assess_answer(legacy, case, prompt_for(case), "legacy")["epistemic_success"])
        self.assertEqual(SYSTEMS["legacy"], SYSTEM)

    def test_known_branch_with_unknown_urgent_is_not_over_abstained(self):
        case = make_state_case(101, "hold-dominates", "test")
        answer = answer_for(case)
        self.assertTrue(answer["value"].startswith("HOLD"))
        self.assertEqual(answer["flags"]["urgent"], "unknown")
        self.assertTrue(assess_answer(json.dumps(answer), case, prompt_for(case), "evidence-state")["recovered"])
        answer.update(status="unknown", value=None)
        self.assertFalse(assess_answer(json.dumps(answer), case, prompt_for(case), "evidence-state")["value_correct"])

    def test_unknown_never_defaults_to_base_and_flag_fidelity_is_independent(self):
        case = make_state_case(101, "hold-unknown", "test")
        answer = answer_for(case)
        policy = next(r for r in case["records"] if r["kind"] == "policy")
        answer.update(status="known", value=policy["base"])
        a = assess_answer(json.dumps(answer), case, prompt_for(case), "evidence-state")
        self.assertTrue(a["unsupported_concrete"])
        answer = answer_for(case)
        answer["flags"]["hold"] = "disabled"
        a = assess_answer(json.dumps(answer), case, prompt_for(case), "evidence-state")
        self.assertTrue(a["epistemic_success"])
        self.assertFalse(a["flags_faithful"])
        self.assertFalse(a["contract_success"])

    def test_empty_and_partial_sources_are_epistemic_not_world_answers(self):
        case = make_state_case(101, "complete-join", "test")
        assignment = next(r for r in case["records"] if r["kind"] == "assignment")
        for visible in ([], [assignment["id"]]):
            answer = answer_for(case, visible)
            a = assess_answer(json.dumps(answer), case, prompt_for(case, visible), "evidence-state")
            self.assertTrue(a["contract_success"])
            self.assertFalse(a["recovered"])
            self.assertIsNone(answer["value"])
            self.assertEqual(answer["evidence"], visible)
        route = make_state_case(101, "base-route", "test")
        self.assertEqual(reference_state(route, [])["flags"], {"urgent": "unobserved", "hold": "unobserved"})

    def test_invisible_irrelevant_or_missing_uncertainty_evidence_fails(self):
        case = make_state_case(101, "pending-join", "test")
        answer = answer_for(case)
        prompt = prompt_for(case)
        for evidence in ([], ["m999"], [r["id"] for r in case["records"] if r["kind"] == "distractor"][:1]):
            answer["evidence"] = evidence
            self.assertFalse(assess_answer(json.dumps(answer), case, prompt, "evidence-state")["contract_success"])

    def test_verbal_unknown_is_not_a_fabricated_concrete_answer(self):
        case = make_state_case(101, "pending-join", "test")
        answer = answer_for(case)
        answer.update(status="known", value="まだ決まっていない")
        a = assess_answer(json.dumps(answer), case, prompt_for(case), "evidence-state")
        self.assertFalse(a["value_correct"])
        self.assertFalse(a["unsupported_concrete"])
        self.assertTrue(a["unrecognized_value"])

    def test_duplicate_nonfinite_malformed_status_and_flags_fail_closed(self):
        case = make_state_case(101, "hold-unknown", "test")
        good = answer_for(case)
        malformed = ["[]", "null", '{"value":null,"value":null}', '{"value":NaN}',
                     json.dumps({**good, "status": "known"}), json.dumps({**good, "value": False}),
                     json.dumps({**good, "flags": {"urgent": False, "hold": "unknown"}}),
                     json.dumps({**good, "flags": {}}), json.dumps({**good, "extra": 1}),
                     json.dumps({**good, "evidence": ["m001", "m001"]}),
                     json.dumps({**good, "evidence": [["m001"]]})]
        for raw in malformed:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_answer(raw, case["family"])
            self.assertFalse(assess_answer(raw, case, prompt_for(case), "evidence-state")["schema_ok"])


class UncertaintyExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_plan(SPEC, CFG)

    def fixture(self, out):
        plan = deepcopy(self.plan)
        digest = canonical_json_sha256(plan)
        write_manifest(out / "plan.json", {"plan_sha256": digest, "plan": plan})
        return plan, digest

    def provider(self, plan):
        by_prompt = {(c["prompt"], plan["systems"][c["variant"]]): c for c in plan["cells"]}

        def call(cfg, prompt, system):
            cell = by_prompt[(prompt, system)]
            case = next(c for c in plan["cases"] if c["id"] == cell["case_id"])
            answer = answer_for(case, cell["visible_ids"])
            if cell["variant"] != "evidence-state":
                answer = {k: answer[k] for k in ("value", "evidence")}
                if answer["value"] is None:
                    answer["evidence"] = []
            return {"content": json.dumps(answer), "response_model": "mistral-large-4",
                    "finish_reason": "stop", "response_id": cell["id"],
                    "request_params": request_params(cfg),
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        return call

    def test_frozen_plan_balanced_and_case_truth_never_enters_prompts(self):
        self.assertEqual(json.loads(SPEC_PATH.read_text()), SPEC)
        self.assertEqual(len(self.plan["cells"]), 84)
        self.assertEqual(self.plan["budget"]["max_output_tokens"], 344064)
        for case in self.plan["cases"]:
            rows = [c for c in self.plan["cells"] if c["case_id"] == case["id"]]
            if case["split"] != "pilot":
                continue
            for condition in SPEC["conditions"]:
                variants = [r for r in rows if r["condition"] == condition]
                self.assertEqual(len(variants), 3)
                self.assertEqual(len({r["prompt_sha256"] for r in variants}), 1)
            self.assertNotIn('"flag_states"', rows[0]["prompt"])
            self.assertEqual(reference_state(case), case["truth"])
        self.assertEqual(len({c["seed"] for c in self.plan["cases"]}), 18)
        self.assertTrue(all(c["seed"] > 26102899 for c in self.plan["cases"]))

    def test_all_reference_answers_pass_and_unobserved_flags_stay_separate(self):
        for cell in self.plan["cells"]:
            if cell["variant"] != "evidence-state":
                continue
            case = next(c for c in self.plan["cases"] if c["id"] == cell["case_id"])
            raw = json.dumps(answer_for(case, cell["visible_ids"]))
            self.assertTrue(assess_answer(raw, case, cell["prompt"], cell["variant"])["contract_success"])

    def test_v21_only_clarifies_example_and_uses_fresh_cohort_same_assessor(self):
        self.assertEqual(json.loads((REPO / "scenarios/uncertainty_contract_v21.json").read_text()), SPEC_V21)
        revised = build_plan(SPEC_V21, CFG)
        self.assertEqual(revised["method"], "evidence-state-v2.1")
        self.assertEqual(len(revised["cells"]), 84)
        self.assertEqual(revised["systems"]["legacy"], self.plan["systems"]["legacy"])
        self.assertEqual(revised["systems"]["guarded-legacy"], self.plan["systems"]["guarded-legacy"])
        self.assertTrue(revised["systems"]["evidence-state"].startswith(self.plan["systems"]["evidence-state"]))
        self.assertFalse({c["seed"] for c in revised["cases"]} & {c["seed"] for c in self.plan["cases"]})
        for cell in revised["cells"]:
            if cell["variant"] == "evidence-state":
                case = next(c for c in revised["cases"] if c["id"] == cell["case_id"])
                raw = json.dumps(answer_for(case, cell["visible_ids"]))
                self.assertTrue(assess_answer(raw, case, cell["prompt"], cell["variant"])["contract_success"])

    def test_gold_changes_cannot_select_retrieval(self):
        from great_scratchpad.memory_task_design import build_conditions
        case = make_state_case(101, "pending-join", "test")
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "notes"
            build_conditions(case, SPEC, archive)
            before = linked_condition(case, SPEC, archive)
            case["truth"] = {"support": [], "value": "FORGED999"}
            after = linked_condition(case, SPEC, archive)
            self.assertEqual(before["prompt_sha256"], after["prompt_sha256"])
            self.assertNotIn("FORGED999", after["prompt"])

    def test_budget_rejected_and_existing_directory_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "run"
            with self.assertRaises(ValueError):
                prepare(out, SPEC_PATH, CONFIG, 83, 344064, 2000000)
            self.assertFalse(out.exists())
            out.mkdir()
            with self.assertRaises(FileExistsError):
                prepare(out, SPEC_PATH, CONFIG, 84, 344064, 2000000)

    def test_changed_spec_profile_and_runtime_rejected_before_calls(self):
        with self.assertRaises(ValueError):
            build_plan({**SPEC, "pilot_seed": 1}, CFG)
        with self.assertRaises(ValueError):
            build_plan(SPEC, {**CFG, "timeout": 120})
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            _, digest = self.fixture(out)
            with patch("great_scratchpad.uncertainty_experiment.runtime_hashes", return_value={}):
                with self.assertRaises(ValueError):
                    load_plan(out, digest, CONFIG)

    def test_mocked_end_to_end_and_raw_audit_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            plan, digest = self.fixture(out)
            with patch("great_scratchpad.uncertainty_experiment.api_key_from_config", return_value="test-secret"), \
                    patch("great_scratchpad.uncertainty_experiment.call_llm_result", side_effect=self.provider(plan)) as call:
                calibration = run(out, digest, CONFIG, "calibration")
                self.assertTrue(calibration["all_contracts_passed"])
                pilot = run(out, digest, CONFIG, "pilot")
                self.assertEqual(call.call_count, 84)
                self.assertEqual(pilot["status"], "complete")
                summary = summarize(plan, pilot)
                self.assertEqual(len(summary["groups"]), 9)
                with self.assertRaises(FileExistsError):
                    run(out, digest, CONFIG, "pilot")
                self.assertEqual(call.call_count, 84)
            self.assertEqual(audit_stage(plan, digest, out, "pilot"), pilot)
            pilot["cells"][0]["assessment"]["schema_ok"] = False
            write_manifest(out / "pilot/result.json", pilot)
            with self.assertRaises(ValueError):
                audit_stage(plan, digest, out, "pilot")

    def test_client_error_retained_no_retry_and_blocks_pilot_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            plan, digest = self.fixture(out)
            provider = self.provider(plan)
            attempted = []

            def failing(cfg, prompt, system):
                attempted.append(prompt)
                if len(attempted) == 1:
                    raise TimeoutError("test-secret")
                return provider(cfg, prompt, system)

            with patch("great_scratchpad.uncertainty_experiment.api_key_from_config", return_value="test-secret"), \
                    patch("great_scratchpad.uncertainty_experiment.call_llm_result", side_effect=failing) as call:
                result = run(out, digest, CONFIG, "calibration")
                self.assertEqual(result["status"], "complete")
                self.assertEqual(result["unavailable_usage_calls"], 1)
                self.assertFalse(result["all_contracts_passed"])
                self.assertEqual(call.call_count, 12)
                with self.assertRaises(ValueError):
                    run(out, digest, CONFIG, "pilot")
                self.assertEqual(call.call_count, 12)
            receipts = (out / "calibration/responses.jsonl").read_text()
            self.assertNotIn("test-secret", receipts)
            self.assertIn("[REDACTED]", receipts)
            self.assertEqual(audit_stage(plan, digest, out, "calibration"), result)

    def test_output_limit_is_failed_even_if_partial_answer_valid(self):
        cell = self.plan["cells"][0]
        response = self.provider(self.plan)(self.plan["config"], cell["prompt"], self.plan["systems"][cell["variant"]])
        receipt = {"raw_output": response["content"], "llm": {"response_model": "mistral-large-4"},
                   "request_params": response["request_params"], "finish_reason": "length"}
        a = assess_receipt(self.plan, cell, receipt)
        self.assertTrue(a["schema_ok"])
        self.assertFalse(a["contract_success"])

    def test_wrong_response_identity_stops_without_attempting_remaining_cells(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            plan, digest = self.fixture(out)
            cell = plan["cells"][0]
            response = self.provider(plan)(plan["config"], cell["prompt"], plan["systems"][cell["variant"]])
            response["response_model"] = "substituted-model"
            with patch("great_scratchpad.uncertainty_experiment.api_key_from_config", return_value="test-secret"), \
                    patch("great_scratchpad.uncertainty_experiment.call_llm_result", return_value=response) as call:
                result = run(out, digest, CONFIG, "calibration")
                self.assertEqual(result["status"], "stopped-identity-mismatch")
                self.assertEqual(call.call_count, 1)
            with self.assertRaises(ValueError):
                audit_stage(plan, digest, out, "calibration")


if __name__ == "__main__":
    unittest.main()
