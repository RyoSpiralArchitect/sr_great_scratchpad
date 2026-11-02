from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from great_scratchpad.dialogue import canonical_json_sha256
from great_scratchpad.experiments import write_manifest
from great_scratchpad.llm import LLMResponseError, OPENAI_CHAT_ADAPTER, call_openai_responses_result, resolve_llm_adapter
from great_scratchpad.luna_uncertainty import (
    CONFIG, PARENTS, SPEC, VARIANTS, assess, audit, build_plan, config, failure_tags,
    load_histories, load_plan, prepare, request_params, run, status, summarize,
)
from great_scratchpad.storage import load_llm_config
from great_scratchpad.task_contract import PROOF_INSTRUCTIONS, declare_task, task_schema
from great_scratchpad.uncertainty_contract import assess_answer, reference_state
from great_scratchpad.uncertainty_experiment import (
    SPEC as MISTRAL_SPEC, SPEC_V21, build_plan as mistral_plan, request_params as mistral_params,
)

REPO = Path(__file__).resolve().parents[1]
CFG_PATH = str(REPO / "examples/gpt-6-luna.json")
SPEC_PATH = REPO / "scenarios/luna_uncertainty_v3.json"


def answer_for(case, visible):
    expected = reference_state(case, visible)
    return {"status": expected["status"], "value": expected["value"],
            "evidence": expected["support"], "flags": expected["flags"]}


def mock_histories():
    cfg = load_llm_config(REPO, str(REPO / "examples/mistral-large-4.json"), "mistral-large-4-high")
    histories = []
    for label, spec in (("v2", MISTRAL_SPEC), ("v2.1", SPEC_V21)):
        plan = mistral_plan(spec, cfg)
        cells = [c for c in plan["cells"] if c["stage"] == "calibration"]
        cases = [c for c in plan["cases"] if c["split"] == "calibration"]
        receipts, saved = [], []
        for cell in cells:
            case = next(c for c in cases if c["id"] == cell["case_id"])
            raw = json.dumps(answer_for(case, cell["visible_ids"]))
            receipt = {"id": cell["id"], "raw_output": raw,
                       "llm": {"response_model": "mistral-large-4"},
                       "request_params": mistral_params(plan["config"]), "finish_reason": "stop"}
            a = assess_answer(raw, case, cell["prompt"], "evidence-state")
            saved.append({"id": cell["id"], "response_sha256": canonical_json_sha256(receipt), "assessment": a})
            receipts.append(receipt)
        histories.append({"cohort": label, "witness": PARENTS[label], "config": plan["config"],
                          "source_commit": "fixture", "system": plan["systems"]["evidence-state"],
                          "cells": cells, "cases": cases, "receipts": receipts, "saved": saved,
                          "known_usage": {"total_tokens": 0}})
    return histories


class ResponsesReceiptTests(unittest.TestCase):
    def test_gpt6_auto_selects_responses_but_explicit_chat_remains_authoritative(self):
        cfg = {"backend": "openai", "adapter": "auto", "model": "gpt-6-luna"}
        self.assertEqual(resolve_llm_adapter(cfg), "openai-responses")
        self.assertEqual(resolve_llm_adapter({**cfg, "adapter": "chat-completions"}), OPENAI_CHAT_ADAPTER)

    def call(self, payload, received_failure=False):
        wire = io.BytesIO(json.dumps(payload).encode())
        with patch("great_scratchpad.llm.api_key_from_config", return_value="fake-key"), \
                patch("great_scratchpad.llm.urllib.request.urlopen", return_value=wire) as post:
            if received_failure:
                with self.assertRaises(LLMResponseError) as caught:
                    call_openai_responses_result(CONFIG, "test user prompt", "test system prompt")
                result = caught.exception.result
            else:
                result = call_openai_responses_result(CONFIG, "test user prompt", "test system prompt")
        sent = json.loads(post.call_args.args[0].data)
        return result, sent

    def test_complete_response_keeps_status_parameters_and_reported_usage(self):
        payload = {"id": "resp_fixture", "status": "completed", "model": "gpt-6-luna",
                   "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
                   "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
        result, sent = self.call(payload)
        self.assertEqual(result["response_status"], "completed")
        self.assertEqual(result["request_params"], request_params(CONFIG))
        self.assertTrue(result["usage_reported"])
        self.assertEqual(result["usage"]["completion_tokens"], 5)
        self.assertEqual(sent["input"], "test user prompt")
        for key in ("input", "instructions", "temperature", "top_p", "seed"):
            self.assertNotIn(key, result["request_params"])

    def test_empty_output_limit_retains_known_reasoning_usage(self):
        result, _ = self.call({"id": "resp_limit", "status": "incomplete", "model": "gpt-6-luna",
                               "output": [], "incomplete_details": {"reason": "max_output_tokens"},
                               "usage": {"input_tokens": 10, "output_tokens": 4096, "total_tokens": 4106}}, received_failure=True)
        self.assertEqual(result["content"], "")
        self.assertTrue(result["usage_reported"])
        self.assertEqual(result["usage"]["completion_tokens"], 4096)
        self.assertEqual(result["incomplete_details"]["reason"], "max_output_tokens")

    def test_empty_incomplete_usage_is_unknown_not_estimated_zero(self):
        result, _ = self.call({"status": "incomplete", "output": [],
                               "incomplete_details": {"reason": "max_output_tokens"}}, received_failure=True)
        self.assertFalse(result["usage_reported"])
        self.assertEqual(result["usage"], {})

    def test_completed_without_text_still_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.call({"status": "completed", "output": []})

    def test_failed_response_retains_error_without_inventing_text(self):
        result, _ = self.call({"status": "failed", "output": [], "error": {"code": "server_error"}}, received_failure=True)
        self.assertEqual(result["response_error"], {"code": "server_error"})
        self.assertEqual(result["content"], "")


class LunaCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.histories = mock_histories()
        cls.plan = build_plan(CONFIG, cls.histories)

    def fixture(self, out):
        plan = deepcopy(self.plan)
        digest = canonical_json_sha256(plan)
        write_manifest(out / "plan.json", {"plan_sha256": digest, "plan": plan})
        return plan, digest

    def provider(self, plan):
        by_input = {(c["prompt"], c["system"]): c for c in plan["cells"]}

        def call(cfg, prompt, system):
            c = by_input[(prompt, system)]
            case = next(case for case in plan["cases"] if case["id"] == c["case_id"])
            return {"content": json.dumps(answer_for(case, c["visible_ids"])),
                    "response_model": "gpt-6-luna", "response_status": "completed",
                    "response_id": "resp_fixture", "request_params": request_params(cfg),
                    "usage_reported": True, "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        return call

    def test_spec_profile_and_budget_are_frozen_without_sampling_overrides(self):
        self.assertEqual(json.loads(SPEC_PATH.read_text()), SPEC)
        self.assertEqual(config(load_llm_config(REPO, CFG_PATH, CONFIG["profile"])), CONFIG)
        self.assertEqual(len(self.plan["cells"]), 84)
        self.assertEqual(self.plan["budget"]["max_output_tokens"], 344064)
        for bad in ({"temperature": 0}, {"seed": 1}, {"model": "gpt-luna-6"},
                    {"api_key": "fake-key"}, {"store": True}, {"reasoning_effort": "low"}):
            with self.assertRaises(ValueError):
                config({**CONFIG, **bad})

    def test_replication_inputs_and_assessments_are_identical_to_parent_cells(self):
        for h in self.histories:
            rows = [c for c in self.plan["cells"] if c["stage"] == "replication" and c["cohort"] == h["cohort"]]
            self.assertEqual(len(rows), 12)
            for row, old, saved in zip(rows, h["cells"], h["saved"]):
                self.assertEqual(row["prompt"], old["prompt"])
                self.assertEqual(row["system"], h["system"])
                self.assertEqual(row["mistral"]["assessment"], saved["assessment"])

    def test_missing_parent_slot_is_not_silently_dropped(self):
        histories = deepcopy(self.histories)
        histories[0]["receipts"].pop()
        with self.assertRaises(ValueError):
            build_plan(CONFIG, histories)

    def test_fresh_cases_disjoint_and_factor_views_preserve_sources(self):
        old_cases = {c["seed"] for h in self.histories for c in h["cases"]}
        fresh_cases = {c["seed"] for c in self.plan["cases"] if c["split"] == "luna-fresh"}
        self.assertEqual(len(fresh_cases), 10)
        self.assertFalse(old_cases & fresh_cases)
        rows = [c for c in self.plan["cells"] if c["stage"] == "fresh"]
        views = {(c["case_id"], c["condition"]) for c in rows}
        self.assertEqual(len(views), 15)
        for case_id, condition in views:
            arms = {c["variant"]: c for c in rows if c["case_id"] == case_id and c["condition"] == condition}
            self.assertEqual(set(arms), set(VARIANTS))
            base = arms["generic"]
            self.assertEqual(base["prompt"], arms["proof"]["prompt"])
            self.assertEqual(arms["task-kind"]["prompt"], arms["task-kind+proof"]["prompt"])
            self.assertTrue(arms["task-kind"]["prompt"].endswith(base["prompt"]))
            self.assertEqual(arms["proof"]["system"], base["system"] + PROOF_INSTRUCTIONS)
            for arm in arms.values():
                self.assertEqual(arm["visible_ids"], base["visible_ids"])
                self.assertEqual(arm["expected"], base["expected"])

    def test_task_schema_is_task_specific_and_not_a_source_of_answers(self):
        routing = task_schema("scoped-exception")["properties"]["flags"]
        self.assertEqual(routing["required"], ["urgent", "hold"])
        for family in ("decision-update", "distributed-join"):
            self.assertEqual(task_schema(family)["properties"]["flags"]["maxProperties"], 0)
        self.assertIn("Declared task kind: distributed-join", declare_task("sentinel", "distributed-join"))
        with self.assertRaises(ValueError):
            task_schema("unknown")

    def test_partial_rule_and_chain_are_unknown_without_losing_available_evidence(self):
        rows = [c for c in self.plan["cells"] if c["stage"] == "fresh" and c["condition"].startswith("partial")]
        self.assertEqual(len(rows), 8)
        for c in rows:
            self.assertEqual(c["expected"]["status"], "unknown")
            self.assertEqual(len(c["expected"]["support"]), 2)
            if c["condition"] == "partial-rule":
                self.assertEqual(c["expected"]["flags"], {"urgent": "enabled", "hold": "disabled"})

    def test_correct_value_missing_citation_is_not_tagged_wrong_value(self):
        c = next(c for c in self.plan["cells"] if c["stage"] == "fresh" and c["scenario"] == "urgent-enabled" and c["condition"] == "source")
        case = next(case for case in self.plan["cases"] if case["id"] == c["case_id"])
        answer = answer_for(case, c["visible_ids"])
        answer["evidence"].remove("m005")
        a = assess_answer(json.dumps(answer), case, c["prompt"], "evidence-state")
        self.assertTrue(a["unsupported_concrete"])
        self.assertFalse(a["contract_success"])
        self.assertIn("missing-citation", failure_tags(json.dumps(answer), a))
        self.assertNotIn("wrong-value", failure_tags(json.dumps(answer), a))

    def test_unknown_to_disabled_and_foreign_flag_shapes_are_separate_tags(self):
        for c in [c for c in self.plan["cells"] if c["stage"] == "fresh" and c["variant"] == "generic"]:
            case = next(case for case in self.plan["cases"] if case["id"] == c["case_id"])
            answer = answer_for(case, c["visible_ids"])
            if c["scenario"] == "hold-unknown" and c["condition"] == "source":
                answer["flags"]["hold"] = "disabled"
                a = assess_answer(json.dumps(answer), case, c["prompt"], "evidence-state")
                self.assertIn("unknown-as-disabled", failure_tags(json.dumps(answer), a))
            if c["scenario"] == "complete-join" and c["condition"] == "empty":
                answer["flags"] = {"urgent": "unobserved", "hold": "unobserved"}
                a = assess_answer(json.dumps(answer), case, c["prompt"], "evidence-state")
                self.assertIn("flag-shape", failure_tags(json.dumps(answer), a))

    def test_simulated_full_campaign_audit_summary_and_no_reissue(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            plan, digest = self.fixture(out)
            with patch("great_scratchpad.luna_uncertainty.api_key_from_config", return_value="test-secret"), \
                    patch("great_scratchpad.luna_uncertainty.call_llm_result", side_effect=self.provider(plan)) as call:
                result = run(out, digest, CFG_PATH)
                self.assertEqual(call.call_count, 84)
                self.assertEqual(result["known_usage"]["total_tokens"], 1260)
                self.assertEqual(result, audit(plan, digest, out))
                summary = summarize(plan, result)
                self.assertEqual(len(summary["replication"]), 2)
                self.assertEqual(len(summary["fresh"]), 4)
                self.assertTrue(all(r["all_15_passed"] for r in summary["fresh"]))
                self.assertEqual(summary["pilot_calls"], 0)
                with self.assertRaises(FileExistsError):
                    run(out, digest, CFG_PATH)
                self.assertEqual(call.call_count, 84)
            result["cells"][0]["assessment"]["contract_success"] = False
            write_manifest(out / "execution/result.json", result)
            with self.assertRaises(ValueError):
                audit(plan, digest, out)

    def test_client_error_retained_and_no_retry_or_zero_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            plan, digest = self.fixture(out)
            provider = self.provider(plan)
            count = 0

            def call(cfg, prompt, system):
                nonlocal count
                count += 1
                if count == 1:
                    raise TimeoutError("test-secret")
                return provider(cfg, prompt, system)

            with patch("great_scratchpad.luna_uncertainty.api_key_from_config", return_value="test-secret"), \
                    patch("great_scratchpad.luna_uncertainty.call_llm_result", side_effect=call):
                result = run(out, digest, CFG_PATH)
            self.assertEqual(count, 84)
            self.assertEqual(result["unavailable_usage_calls"], 1)
            self.assertFalse(result["cells"][0]["assessment"]["contract_success"])
            self.assertNotIn("test-secret", (out / "execution/responses.jsonl").read_text())
            self.assertEqual(audit(plan, digest, out), result)

    def test_identity_or_reflected_secret_stops_campaign(self):
        for unsafe in (False, True):
            with tempfile.TemporaryDirectory() as temporary:
                out = Path(temporary)
                plan, digest = self.fixture(out)
                first = plan["cells"][0]
                response = self.provider(plan)(CONFIG, first["prompt"], first["system"])
                response["content" if unsafe else "response_model"] = "test-secret" if unsafe else "other-model"
                with patch("great_scratchpad.luna_uncertainty.api_key_from_config", return_value="test-secret"), \
                        patch("great_scratchpad.luna_uncertainty.call_llm_result", return_value=response) as call:
                    result = run(out, digest, CFG_PATH)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(result["status"], "stopped-identity-or-security")
                self.assertNotIn("test-secret", (out / "execution/responses.jsonl").read_text())
                with self.assertRaises(ValueError):
                    audit(plan, digest, out)

    def test_valid_json_on_output_limit_never_counts_as_success(self):
        c = self.plan["cells"][0]
        response = self.provider(self.plan)(CONFIG, c["prompt"], c["system"])
        receipt = {"raw_output": response["content"], "llm": {"response_model": "gpt-6-luna"},
                   "request_params": response["request_params"], "response_status": "incomplete",
                   "incomplete_details": {"reason": "max_output_tokens"}}
        self.assertEqual(status(receipt), "output-limit")
        a = assess(self.plan, c, receipt)
        self.assertTrue(a["schema_ok"])
        self.assertFalse(a["contract_success"])

    def test_schema_runtime_and_budget_drift_rejected_before_paid_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "run"
            with patch("great_scratchpad.luna_uncertainty.load_histories", return_value=self.histories):
                with self.assertRaises(ValueError):
                    prepare(out, Path(temporary), SPEC_PATH, CFG_PATH, 83, 344064, 2000000)
            self.assertFalse(out.exists())
            out.mkdir()
            _, digest = self.fixture(out)
            with patch("great_scratchpad.luna_uncertainty.runtime_hashes", return_value={}):
                with self.assertRaises(ValueError):
                    load_plan(out, digest, CFG_PATH)
            with patch("great_scratchpad.luna_uncertainty.sha", return_value="changed-schema"):
                with self.assertRaises(ValueError):
                    load_plan(out, digest, CFG_PATH)

    def test_altered_historical_files_rejected_before_loading_assessments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for witness in PARENTS.values():
                for file in witness["files"]:
                    write_manifest(root / witness["directory"] / file, {})
            with self.assertRaises(ValueError):
                load_histories(root)


if __name__ == "__main__":
    unittest.main()
